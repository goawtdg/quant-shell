"""财联社电报情报源 — 直连 v1 API。"""
from __future__ import annotations

from datetime import datetime, timezone

from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import IntelligenceItem
from quant_shell.intelligence.client import run_source_fetch
from quant_shell.intelligence.providers.cls_api import fetch_cls_telegraph
from quant_shell.intelligence.constants import (
    MAX_ITEMS_PER_SOURCE,
    SOURCE_CLS,
    SOURCE_TIER,
)
from quant_shell.intelligence.normalizer import build_item, normalize_text
from quant_shell.intelligence.sources.base import IntelligenceSource

logger = get_logger(__name__)


class ClsTelegraphSource(IntelligenceSource):
    """财联社电报 — https://www.cls.cn/telegraph"""

    name = SOURCE_CLS

    def fetch(self, symbol: str = "") -> list[IntelligenceItem]:
        """拉取财联社快讯。"""
        del symbol
        rows = run_source_fetch(self.name, lambda: fetch_cls_telegraph(rn=MAX_ITEMS_PER_SOURCE))
        return self._parse_rows(rows)

    def _parse_rows(self, rows: list[dict[str, object]]) -> list[IntelligenceItem]:
        items: list[IntelligenceItem] = []
        for row in rows[:MAX_ITEMS_PER_SOURCE]:
            title = normalize_text(str(row.get("title") or row.get("brief") or ""))
            content = normalize_text(str(row.get("content") or row.get("brief") or title))
            published = _parse_ctime(row.get("ctime"))
            items.append(
                build_item(
                    source=self.name,
                    source_tier=SOURCE_TIER[self.name],
                    title=title,
                    content=content,
                    published_at=published,
                    url=f"https://www.cls.cn/detail/{row.get('id')}" if row.get("id") else "",
                    importance=str(row.get("level") or ""),
                )
            )
        logger.info("ClsTelegraphSource fetched=%d", len(items))
        return items


def _parse_ctime(value: object) -> datetime:
    """解析财联社 ctime 时间戳。"""
    try:
        ts = int(value)  # type: ignore[arg-type]
        return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return datetime.now()
