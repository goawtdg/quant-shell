"""同花顺财经直播情报源 — 直连 push API。"""
from __future__ import annotations

from datetime import datetime, timezone

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import IntelligenceItem
from quant_shell.intelligence.client import run_source_fetch
from quant_shell.intelligence.providers.ths_api import fetch_ths_flash
from quant_shell.intelligence.constants import (
    MAX_ITEMS_PER_SOURCE,
    SOURCE_THS,
    SOURCE_TIER,
)
from quant_shell.intelligence.normalizer import build_item, normalize_text
from quant_shell.intelligence.sources.base import IntelligenceSource

logger = get_logger(__name__)


class ThsRealtimeSource(IntelligenceSource):
    """同花顺全球财经直播 — news.10jqka.com.cn/tapp/news/push/stock"""

    name = SOURCE_THS

    def fetch(self, symbol: str = "") -> list[IntelligenceItem]:
        """拉取同花顺快讯。"""
        del symbol
        rows = run_source_fetch(self.name, lambda: fetch_ths_flash(page=1))
        return self._parse_rows(rows)

    def _parse_rows(self, rows: list[dict[str, object]]) -> list[IntelligenceItem]:
        items: list[IntelligenceItem] = []
        for row in rows[:MAX_ITEMS_PER_SOURCE]:
            title = normalize_text(str(row.get("title") or ""))
            content = normalize_text(str(row.get("digest") or title))
            published = _parse_rtime(row.get("rtime") or row.get("ctime"))
            items.append(
                build_item(
                    source=self.name,
                    source_tier=SOURCE_TIER[self.name],
                    title=title,
                    content=content,
                    published_at=published,
                    url=str(row.get("url") or row.get("shareUrl") or ""),
                )
            )
        logger.info("ThsRealtimeSource fetched=%d", len(items))
        return items


def _parse_rtime(value: object) -> datetime:
    """解析同花顺 rtime/ctime 时间戳。"""
    try:
        ts = int(value)  # type: ignore[arg-type]
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return datetime.now()
