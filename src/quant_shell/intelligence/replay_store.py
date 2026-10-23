"""情报回放样本 — 最近一次成功采集落在磁盘上。"""
from __future__ import annotations

from datetime import datetime

from quant_shell.common.types import IntelligenceItem
from quant_shell.data.disk_cache import CACHE_ROOT, load_json_record, save_json_record


def global_path():
    return CACHE_ROOT / "intel" / "global.json"


def symbol_path(symbol: str):
    return CACHE_ROOT / "intel" / f"{symbol}.json"


def intel_ttl_sec() -> float:
    from quant_shell.config.settings import settings

    minutes = float(getattr(settings, "intel_cache_max_age_min", 120) or 120)
    if minutes <= 0:
        return 0.0
    return minutes * 60.0


def load_items(path, *, allow_stale: bool = False) -> list[IntelligenceItem] | None:
    raw = load_json_record(path, intel_ttl_sec(), allow_stale=allow_stale)
    if not isinstance(raw, list) or not raw:
        return None
    items: list[IntelligenceItem] = []
    for row in raw:
        item = _item_from_record(row)
        if item is not None:
            items.append(item)
    return items or None


def save_items(path, items: list[IntelligenceItem]) -> None:
    if not items:
        return
    save_json_record(path, [_item_to_record(item) for item in items])


def _item_to_record(item: IntelligenceItem) -> dict[str, object]:
    return {
        "item_id": item.item_id,
        "source": item.source,
        "source_tier": item.source_tier,
        "title": item.title,
        "content": item.content,
        "published_at": item.published_at.isoformat(),
        "url": item.url,
        "entities": list(item.entities),
        "event_tags": list(item.event_tags),
        "symbol_hint": item.symbol_hint,
        "importance": item.importance,
    }


def _item_from_record(row: object) -> IntelligenceItem | None:
    if not isinstance(row, dict) or not row.get("item_id"):
        return None
    raw_ts = row.get("published_at")
    try:
        published = datetime.fromisoformat(str(raw_ts)) if raw_ts else datetime.now()
    except ValueError:
        published = datetime.now()
    return IntelligenceItem(
        item_id=str(row.get("item_id")),
        source=str(row.get("source") or ""),
        source_tier=int(row.get("source_tier") or 2),
        title=str(row.get("title") or ""),
        content=str(row.get("content") or ""),
        published_at=published,
        url=str(row.get("url") or ""),
        entities=[str(x) for x in (row.get("entities") or [])],
        event_tags=[str(x) for x in (row.get("event_tags") or [])],
        symbol_hint=str(row.get("symbol_hint") or ""),
        importance=str(row.get("importance") or ""),
    )
