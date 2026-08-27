"""新浪财经 7x24 情报源。"""
from __future__ import annotations

import akshare as ak
import pandas as pd

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import IntelligenceItem
from quant_shell.intelligence.client import run_source_fetch
from quant_shell.intelligence.constants import (
    MAX_ITEMS_PER_SOURCE,
    SOURCE_SINA,
    SOURCE_TIER,
)
from quant_shell.intelligence.normalizer import build_item, parse_published
from quant_shell.intelligence.sources.base import IntelligenceSource

logger = get_logger(__name__)


class SinaFlashSource(IntelligenceSource):
    """新浪财经全球财经直播。"""

    name = SOURCE_SINA

    def fetch(self, symbol: str = "") -> list[IntelligenceItem]:
        """拉取新浪快讯。"""
        del symbol
        frame = run_source_fetch(self.name, lambda: ak.stock_info_global_sina())
        return self._parse_frame(frame)

    def _parse_frame(self, frame: pd.DataFrame) -> list[IntelligenceItem]:
        items: list[IntelligenceItem] = []
        for _, row in frame.head(MAX_ITEMS_PER_SOURCE).iterrows():
            content = str(row.get("内容", "") or "")
            items.append(
                build_item(
                    source=self.name,
                    source_tier=SOURCE_TIER[self.name],
                    title=content[:48],
                    content=content,
                    published_at=parse_published(row.get("时间", "")),
                )
            )
        logger.info("SinaFlashSource fetched=%d", len(items))
        return items
