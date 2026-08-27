"""东财个股新闻情报源。"""
from __future__ import annotations

import akshare as ak
import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import IntelligenceItem
from quant_shell.data.constants import SYMBOL_TO_INDEX_NAME
from quant_shell.intelligence.client import run_source_fetch
from quant_shell.intelligence.constants import (
    MAX_ITEMS_PER_SOURCE,
    SOURCE_STOCK_NEWS,
    SOURCE_TIER,
)
from quant_shell.intelligence.normalizer import build_item, parse_published
from quant_shell.intelligence.sources.base import IntelligenceSource

logger = get_logger(__name__)


class StockNewsSource(IntelligenceSource):
    """东方财富个股/关键词新闻。"""

    name = SOURCE_STOCK_NEWS
    is_symbol_scoped = True

    def fetch(self, symbol: str = "") -> list[IntelligenceItem]:
        """拉取与 symbol 或指数名相关的新闻。"""
        keywords = self._resolve_keywords(symbol)
        items: list[IntelligenceItem] = []
        for keyword in keywords:
            frame = run_source_fetch(
                f"{self.name}:{keyword}",
                lambda kw=keyword: ak.stock_news_em(symbol=kw),
            )
            items.extend(self._parse_frame(frame, keyword))
        logger.info("StockNewsSource symbol=%s fetched=%d", symbol, len(items))
        return items

    def _resolve_keywords(self, symbol: str) -> list[str]:
        """ETF 映射到指数名，股票直接用代码。"""
        if not symbol:
            return []
        index_name = SYMBOL_TO_INDEX_NAME.get(symbol)
        if index_name:
            return [symbol, index_name]
        return [symbol]

    def _parse_frame(self, frame: pd.DataFrame, keyword: str) -> list[IntelligenceItem]:
        items: list[IntelligenceItem] = []
        for _, row in frame.head(MAX_ITEMS_PER_SOURCE).iterrows():
            items.append(
                build_item(
                    source=self.name,
                    source_tier=SOURCE_TIER[self.name],
                    title=str(row.get("新闻标题", "") or ""),
                    content=str(row.get("新闻内容", "") or ""),
                    published_at=parse_published(row.get("发布时间", "")),
                    url=str(row.get("新闻链接", "") or ""),
                    symbol_hint=keyword,
                )
            )
        return items
