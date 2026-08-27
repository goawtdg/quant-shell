"""统一 L1 数据源 — ETF 与 A 股个股。"""
from __future__ import annotations

from datetime import datetime

from quant_shell.common import audit
from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.interfaces import DataSource
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import MarketSnapshot
from quant_shell.data import akshare_client
from quant_shell.data.constants import DATA_SOURCE_NAME, SYMBOL_TO_INDEX_NAME
from quant_shell.data.pe_quality import (
    PE_SOURCE_ETF_LEGULEGU,
    PE_SOURCE_FALLBACK_ETF_UNMAPPED,
    PE_SOURCE_FALLBACK_PROXY,
    PE_SOURCE_STOCK_HIST,
    PeResolution,
)
from quant_shell.data.stock_client import (
    fetch_stock_daily_ohlcv,
    fetch_stock_pe_percentile,
    fetch_stock_spot,
)
from quant_shell.data.stock_metrics import enrich_ohlcv_metrics
from quant_shell.data.symbol import is_etf

logger = get_logger(__name__)

# 仅诊断用：回退时写入 pe_proxy_over_200，绝不写入 pe_percentile
_STOCK_PE_SANITY_MAX = 200.0
_NEUTRAL_PE_PERCENTILE = 0.5


class UnifiedMarketDataSource(DataSource):
    """ETF 与个股统一行情入口。"""

    def fetch_market(self, symbol: str) -> MarketSnapshot:
        """采集 ETF 或个股市场快照。"""
        if is_etf(symbol):
            return self._fetch_etf(symbol)
        return self._fetch_stock(symbol)

    def _fetch_etf(self, symbol: str) -> MarketSnapshot:
        logger.info("采集 ETF symbol=%s", symbol)
        spot = akshare_client.fetch_etf_spot(symbol)
        if symbol in SYMBOL_TO_INDEX_NAME:
            pe = PeResolution(
                source=PE_SOURCE_ETF_LEGULEGU,
                percentile=akshare_client.fetch_index_pe_percentile(symbol),
                reliable=True,
            )
        else:
            pe = PeResolution(
                source=PE_SOURCE_FALLBACK_ETF_UNMAPPED,
                percentile=_NEUTRAL_PE_PERCENTILE,
                reliable=False,
                reason="ETF无指数PE映射，中性0.5且禁用估值逻辑",
            )
            _emit_pe_unreliable(symbol, pe)
        ohlcv = akshare_client.fetch_etf_daily_ohlcv(symbol)
        return MarketSnapshot(
            symbol=symbol,
            timestamp=datetime.now(),
            price=spot.price,
            volume=spot.volume,
            pe_percentile=pe.percentile,
            extra={
                "source": DATA_SOURCE_NAME,
                "asset_type": "etf",
                "index_name": SYMBOL_TO_INDEX_NAME.get(symbol, ""),
                "ohlcv_bars": len(ohlcv),
                **pe.as_extra(),
            },
        )

    def _fetch_stock(self, symbol: str) -> MarketSnapshot:
        logger.info("采集个股 symbol=%s", symbol)
        spot = fetch_stock_spot(symbol)
        pe_spot = float(spot.get("pe", 0) or 0)
        pe = self._resolve_stock_pe(symbol, pe_spot)
        name = str(spot.get("name", ""))
        ohlcv = fetch_stock_daily_ohlcv(symbol)
        metrics = {"return_5d": 0.0, "return_10d": 0.0, "at_limit_up": False}
        try:
            metrics = enrich_ohlcv_metrics(symbol, name, ohlcv)
        except (DataFetchError, ValidationError, OSError, ValueError, KeyError) as exc:
            audit.emit(
                layer="L1",
                event="layer_error",
                severity="WARN",
                symbol=symbol,
                error_code="STOCK_METRICS_SKIP",
                message=str(exc),
            )
        return MarketSnapshot(
            symbol=symbol,
            timestamp=datetime.now(),
            price=float(spot["price"]),
            volume=float(spot.get("volume", 0) or 0),
            pe_percentile=pe.percentile,
            extra={
                "source": DATA_SOURCE_NAME,
                "asset_type": "stock",
                "name": name,
                "pe": pe_spot,
                "return_5d": float(metrics["return_5d"]),
                "return_10d": float(metrics["return_10d"]),
                "at_limit_up": float(bool(metrics["at_limit_up"])),
                "ohlcv_bars": len(ohlcv),
                **pe.as_extra(),
            },
        )

    def _resolve_stock_pe(self, symbol: str, pe_spot: float) -> PeResolution:
        """优先东财 PE(TTM) 历史分位；失败进入 PeResolution(reliable=False)。"""
        try:
            hist = fetch_stock_pe_percentile(symbol)
            return PeResolution(
                source=PE_SOURCE_STOCK_HIST,
                percentile=float(hist["pe_percentile"]),
                reliable=True,
                pe_ttm=float(hist["pe_ttm"]),
            )
        except (DataFetchError, ValidationError, OSError) as exc:
            proxy = min(pe_spot / _STOCK_PE_SANITY_MAX, 1.0) if pe_spot > 0 else 0.5
            pe = PeResolution(
                source=PE_SOURCE_FALLBACK_PROXY,
                percentile=_NEUTRAL_PE_PERCENTILE,
                reliable=False,
                reason=f"{type(exc).__name__}: {exc}",
                pe_ttm=pe_spot,
                pe_proxy_over_200=proxy,
            )
            _emit_pe_unreliable(symbol, pe)
            return pe


def _emit_pe_unreliable(symbol: str, pe: PeResolution) -> None:
    audit.emit(
        layer="L1",
        event="pe_unreliable",
        severity="ERROR",
        symbol=symbol,
        error_code="PE_UNRELIABLE",
        message=pe.reason or pe.source,
        data={"source": pe.source, "percentile": pe.percentile},
    )
    logger.warning(
        "PE_UNRELIABLE symbol=%s source=%s pe_percentile=%.2f(neutral) reason=%s",
        symbol,
        pe.source,
        pe.percentile,
        pe.reason,
    )
