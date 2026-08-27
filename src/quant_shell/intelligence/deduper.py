"""情报去重与多源印证。"""
from __future__ import annotations

from datetime import datetime, timedelta

from quant_shell.common.types import IntelligenceItem
from quant_shell.intelligence.constants import (
    CORROBORATION_WINDOW_MINUTES,
    TITLE_MATCH_MIN_CHARS,
)
from quant_shell.intelligence.normalizer import normalize_text


def dedupe_items(items: list[IntelligenceItem]) -> list[IntelligenceItem]:
    """按 item_id 去重，保留不同源的相似标题以供印证。"""
    seen_ids: set[str] = set()
    result: list[IntelligenceItem] = []
    for item in sorted(items, key=lambda x: x.published_at, reverse=True):
        if item.item_id in seen_ids:
            continue
        seen_ids.add(item.item_id)
        result.append(item)
    return result


def count_corroborations(items: list[IntelligenceItem]) -> int:
    """统计多源印证事件组数量。"""
    return len(find_corroboration_groups(items))


def find_corroboration_groups(items: list[IntelligenceItem]) -> list[list[IntelligenceItem]]:
    """找出时间窗口内、不同源、标题相似的情报组。"""
    groups: list[list[IntelligenceItem]] = []
    used: set[str] = set()
    sorted_items = sorted(items, key=lambda x: x.published_at, reverse=True)

    for idx, anchor in enumerate(sorted_items):
        if anchor.item_id in used:
            continue
        cluster = [anchor]
        used.add(anchor.item_id)
        for candidate in sorted_items[idx + 1 :]:
            if candidate.item_id in used:
                continue
            if not _is_corroborated(anchor, candidate):
                continue
            cluster.append(candidate)
            used.add(candidate.item_id)
        if len({item.source for item in cluster}) >= 2:
            groups.append(cluster)
    return groups


def _is_corroborated(left: IntelligenceItem, right: IntelligenceItem) -> bool:
    """判断两条情报是否互为印证。"""
    if left.source == right.source:
        return False
    delta = abs(left.published_at - right.published_at)
    if delta > timedelta(minutes=CORROBORATION_WINDOW_MINUTES):
        return False
    return _titles_overlap(left.title, right.title)


def _titles_overlap(left: str, right: str) -> bool:
    """标题相似性（公共子串）。"""
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    for size in range(len(shorter), TITLE_MATCH_MIN_CHARS - 1, -1):
        for start in range(0, len(shorter) - size + 1):
            if shorter[start : start + size] in longer:
                return True
    return False
