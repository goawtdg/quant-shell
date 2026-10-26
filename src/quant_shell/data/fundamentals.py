"""批量基本面数据采集 — 单票现价 + 腾讯日 K + 业绩报表预热，有限并发。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import StockFundamentals
from quant_shell.config.settings import settings
from quant_shell.data.constants import VOLUME_MA_DAYS
from quant_shell.signals.trailing_return import trailing_return
from quant_shell.data.stock_industry import (
    fetch_stock_industry,
    flush_industry_disk_cache,
)
from quant_shell.data.stock_metrics import enrich_ohlcv_metrics
from quant_shell.data.stock_ohlcv import fetch_stock_daily_ohlcv
from quant_shell.data.stock_spot import fetch_stock_spot
from quant_shell.data.stock_yjbb import fetch_stock_roe, prefetch_yjbb_frame

logger = get_logger(__name__)


def build_stock_fundamentals(
    symbol: str,
    *,
    skip_industry: bool = False,
) -> StockFundamentals:
    """构建单只股票基本面快照。行情或收益算不出来时直接失败。"""
    spot = fetch_stock_spot(symbol)
    ohlcv = fetch_stock_daily_ohlcv(symbol)
    close = ohlcv["close"]
    volume = ohlcv["volume"]
    price = float(spot["price"])
    name = str(spot.get("name", ""))
    metrics = enrich_ohlcv_metrics(symbol, name, ohlcv)
    return StockFundamentals(
        symbol=symbol,
        name=name,
        price=price,
        market_cap=float(spot.get("market_cap", 0) or 0),
        pe=float(spot.get("pe", 0) or 0),
        roe=fetch_stock_roe(symbol),
        volume=float(volume.iloc[-1]),
        volume_ma20=float(volume.tail(VOLUME_MA_DAYS).mean()),
        return_3m=trailing_return(close),
        return_5d=float(metrics["return_5d"]),
        return_10d=float(metrics["return_10d"]),
        at_limit_up=bool(metrics["at_limit_up"]),
        turnover_rate=float(spot.get("turnover_rate", 0) or 0),
        industry="未知" if skip_industry else fetch_stock_industry(symbol),
    )


def build_universe_frame(
    symbols: list[str],
    max_symbols: int | None = None,
    *,
    skip_industry: bool = False,
) -> pd.DataFrame:
    """批量构建候选池基本面。

    路径：预热 yjbb 一次 → 并发单票现价 + 腾讯日 K。
    不拉全 A（东财单页硬顶 100，全表约 59 页）。
    """
    subset = symbols if max_symbols in (None, 0) else symbols[:max_symbols]
    workers = max(1, min(int(settings.universe_fetch_workers or 8), 32))
    logger.info(
        "build_universe_frame start total=%d skip_industry=%s workers=%d",
        len(subset),
        skip_industry,
        workers,
    )
    prefetch_yjbb_frame()

    rows: list[dict[str, object]] = []
    done = 0

    def _record(item: StockFundamentals) -> None:
        nonlocal done
        done += 1
        rows.append(item.to_dict())
        if done == 1 or done % 5 == 0 or done == len(subset):
            logger.info(
                "build_universe_frame progress=%d/%d ok=%d",
                done,
                len(subset),
                len(rows),
            )

    if workers <= 1 or len(subset) <= 1:
        for symbol in subset:
            _record(build_stock_fundamentals(symbol, skip_industry=skip_industry))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [
                pool.submit(build_stock_fundamentals, s, skip_industry=skip_industry)
                for s in subset
            ]
            for fut in as_completed(futs):
                _record(fut.result())

    if not skip_industry:
        flush_industry_disk_cache()

    logger.info("build_universe_frame requested=%d ok=%d", len(subset), len(rows))
    return pd.DataFrame(rows)


