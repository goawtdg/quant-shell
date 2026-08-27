"""规则实体与事件标签。"""
from __future__ import annotations

from quant_shell.common.types import IntelligenceItem
from quant_shell.intelligence.constants import ENTITY_KEYWORDS, EVENT_TAG_KEYWORDS


def tag_item(item: IntelligenceItem) -> IntelligenceItem:
    """为情报条目补充 entities / event_tags。"""
    text = f"{item.title} {item.content}"
    entities = [kw for kw in ENTITY_KEYWORDS if kw in text]
    tags: list[str] = []
    for tag, keywords in EVENT_TAG_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            tags.append(tag)
    item.entities = entities
    item.event_tags = tags
    return item


def tag_items(items: list[IntelligenceItem]) -> list[IntelligenceItem]:
    """批量打标签。"""
    return [tag_item(item) for item in items]
