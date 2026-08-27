"""成交用实时市价 — 唯一 TTL 缓存；成交只认 live。"""
from __future__ import annotations

import threading
import time

import pandas as pd

from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.common.retry import call_with_retry
from quant_shell.config.settings import settings
from quant_shell.data import akshare_client
from quant_shell.data.akshare_client import EtfSpotRow
from quant_shell.data.stock_client import fetch_stock_spot_quote
from quant_shell.data.symbol import is_etf

logger = get_logger(__name__)

_SPOT_CODE_COL = "代码"
_SPOT_PRICE_COL = "最新价"
_SPOT_VOLUME_COL = "成交量"

_lock = threading.Lock()
_etf_batch: pd.DataFrame | None = None
_etf_batch_mono: float = 0.0


def _ttl_sec() -> float:
    return float(getattr(settings, "spot_cache_ttl_sec", 600.0) or 600.0)


def _need_etf_refresh(force_refresh: bool | None) -> bool:
    if force_refresh is True:
        return True
    if force_refresh is False:
        return _etf_batch is None
    if _etf_batch is None or _etf_batch_mono <= 0:
        return True
    return (time.monotonic() - _etf_batch_mono) > _ttl_sec()


def clear_live_spot_cache() -> None:
    """清空 ETF TTL 批次（测试用）。"""
    global _etf_batch, _etf_batch_mono
    with _lock:
        _etf_batch = None
        _etf_batch_mono = 0.0


def _ensure_etf_batch(force_refresh: bool | None) -> pd.DataFrame:
    global _etf_batch, _etf_batch_mono
    with _lock:
        if not _need_etf_refresh(force_refresh) and _etf_batch is not None:
            return _etf_batch
        frame = akshare_client.fetch_etf_spot_batch()
        _etf_batch = frame
        _etf_batch_mono = time.monotonic()
        logger.info("live_spot_cache refreshed scope=etf rows=%d", len(frame))
        return frame


def refresh_live_spot_caches(*, etfs: bool = True) -> None:
    """刷新 ETF TTL 批次。个股一律单票报价，不拉全 A。"""
    if etfs:
        _ensure_etf_batch(force_refresh=True)


def lookup_etf_spot(symbol: str, *, force_refresh: bool | None = None) -> EtfSpotRow:
    """从当前 TTL 批次查 ETF 现货；批次没有该代码则 DataFetchError。"""
    batch = _ensure_etf_batch(force_refresh)
    matched = batch.loc[batch[_SPOT_CODE_COL].astype(str).str.zfill(6) == symbol]
    if matched.empty:
        raise DataFetchError(
            message=f"未找到 ETF 代码: {symbol}",
            suggestion="确认代码有效且在东财 ETF 现货全表中",
        )
    hit = matched.iloc[0]
    price = float(hit[_SPOT_PRICE_COL])
    volume = float(hit[_SPOT_VOLUME_COL] or 0)
    if price <= 0:
        raise ValidationError(
            message=f"ETF 现价无效: {symbol}={price}",
            suggestion="检查东财 ETF 现货字段",
        )
    return EtfSpotRow(price=price, volume=volume)


def fetch_live_fill_price(
    symbol: str,
    *,
    force_refresh: bool | None = None,
) -> float:
    """取真实现价，供 L6 模拟成交 / 盯市使用。只认 live，无日 K 收盘兜底。"""
    attempt = {"n": 0}

    def _once() -> float:
        attempt["n"] += 1
        refresh = force_refresh
        if attempt["n"] > 1 and force_refresh is not False:
            refresh = True
        if is_etf(symbol):
            price = float(lookup_etf_spot(symbol, force_refresh=refresh).price)
        else:
            price = float(fetch_stock_spot_quote(symbol)["price"])
        if price <= 0:
            raise ValidationError(
                message=f"实时成交价无效: {symbol}={price}",
                suggestion="检查东财/新浪行情是否正常",
            )
        return price

    price = call_with_retry(
        _once, layer="L1", op="live_fill_price", symbol=symbol
    )
    logger.info(
        "live_fill_price symbol=%s price=%.4f force_refresh=%s",
        symbol,
        price,
        force_refresh,
    )
    return price


def fetch_live_fill_prices(
    symbols: list[str],
    *,
    force_refresh: bool | None = None,
) -> dict[str, float]:
    """批量取价：个股逐票；ETF 在 TTL 内最多刷一次全表。失败标的不写入。"""
    uniq = [s for s in dict.fromkeys(symbols) if s]
    if not uniq:
        return {}
    if any(is_etf(s) for s in uniq) and _need_etf_refresh(force_refresh):
        refresh_live_spot_caches(etfs=True)

    out: dict[str, float] = {}
    for symbol in uniq:
        try:
            out[symbol] = fetch_live_fill_price(
                symbol,
                force_refresh=False if is_etf(symbol) else force_refresh,
            )
        except (DataFetchError, ValidationError, OSError) as exc:
            logger.warning("live_fill_prices skip symbol=%s err=%s", symbol, exc)
    return out
