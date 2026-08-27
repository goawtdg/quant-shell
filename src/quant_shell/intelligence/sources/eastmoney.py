"""东方财富 7x24 快讯情报源。"""
from __future__ import annotations

import akshare as ak
import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import IntelligenceItem
from quant_shell.intelligence.client import run_source_fetch
from quant_shell.intelligence.constants import (
    MAX_ITEMS_PER_SOURCE,
    SOURCE_EASTMONEY,
    SOURCE_TIER,
)
from quant_shell.intelligence.normalizer import build_item, parse_published
from quant_shell.intelligence.sources.base import IntelligenceSource

logger = get_logger(__name__)


class EastmoneyFlashSource(IntelligenceSource):
    """东方财富全球财经快讯。"""

    name = SOURCE_EASTMONEY

    def fetch(self, symbol: str = "") -> list[IntelligenceItem]:
        """拉取东财快讯。"""
        del symbol
        frame = run_source_fetch(self.name, lambda: ak.stock_info_global_em())
        return self._parse_frame(frame)

    def _parse_frame(self, frame: pd.DataFrame) -> list[IntelligenceItem]:
        items: list[IntelligenceItem] = []
        for _, row in frame.head(MAX_ITEMS_PER_SOURCE).iterrows():
            items.append(
                build_item(
                    source=self.name,
                    source_tier=SOURCE_TIER[self.name],
                    title=str(row.get("标题", "") or ""),
                    content=str(row.get("摘要", "") or ""),
                    published_at=parse_published(row.get("发布时间", "")),
                    url=str(row.get("链接", "") or ""),
                )
            )
        logger.info("EastmoneyFlashSource fetched=%d", len(items))
        return items
