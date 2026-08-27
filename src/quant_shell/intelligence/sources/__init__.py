"""情报源注册。"""
from __future__ import annotations

from quant_shell.intelligence.constants import (
    DEFAULT_GLOBAL_SOURCES,
    SOURCE_CLS,
    SOURCE_EASTMONEY,
    SOURCE_SINA,
    SOURCE_STOCK_NEWS,
    SOURCE_THS,
)
from quant_shell.intelligence.sources.base import IntelligenceSource
from quant_shell.intelligence.sources.cls import ClsTelegraphSource
from quant_shell.intelligence.sources.eastmoney import EastmoneyFlashSource
from quant_shell.intelligence.sources.sina import SinaFlashSource
from quant_shell.intelligence.sources.stock_news import StockNewsSource
from quant_shell.intelligence.sources.ths import ThsRealtimeSource

_SOURCE_MAP: dict[str, type[IntelligenceSource]] = {
    SOURCE_CLS: ClsTelegraphSource,
    SOURCE_EASTMONEY: EastmoneyFlashSource,
    SOURCE_THS: ThsRealtimeSource,
    SOURCE_SINA: SinaFlashSource,
    SOURCE_STOCK_NEWS: StockNewsSource,
}


def build_sources(
    enabled: tuple[str, ...] | None = None,
    *,
    include_symbol_news: bool = True,
) -> list[IntelligenceSource]:
    """构建启用的情报源实例。"""
    names = list(enabled or DEFAULT_GLOBAL_SOURCES)
    if include_symbol_news and SOURCE_STOCK_NEWS not in names:
        names.append(SOURCE_STOCK_NEWS)
    return [_SOURCE_MAP[name]() for name in names if name in _SOURCE_MAP]
