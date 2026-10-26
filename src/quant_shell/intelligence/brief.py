"""情报摘要与情绪分计算。"""
from __future__ import annotations

from datetime import datetime

from quant_shell.common.types import IntelligenceBrief, IntelligenceItem, MarketSnapshot
from quant_shell.intelligence.constants import (
    BRIEF_MARKET_RESERVE,
    BRIEF_MIN_MARKET_SOURCES,
    DEFAULT_BRIEF_LIMIT,
    NEGATIVE_KEYWORDS,
    POSITIVE_KEYWORDS,
    SOURCE_STOCK_NEWS,
)
from quant_shell.intelligence.deduper import count_corroborations


def filter_relevant_items(
    items: list[IntelligenceItem],
    symbol: str,
    market: MarketSnapshot | None,
    *,
    limit: int = DEFAULT_BRIEF_LIMIT,
    market_reserve: int = BRIEF_MARKET_RESERVE,
    min_market_sources: int = BRIEF_MIN_MARKET_SOURCES,
) -> list[IntelligenceItem]:
    """筛选与标的相关的情报，并为非 stock_news 市场源预留配额。"""
    if limit <= 0:
        return []
    if not items:
        return []

    keywords = _build_keywords(symbol, market)
    matched = (
        [item for item in items if _matches_keywords(item, keywords)]
        if keywords
        else list(items)
    )
    reserve = max(0, min(market_reserve, limit))
    matched_cap = limit - reserve

    selected: list[IntelligenceItem] = []
    seen_ids: set[str] = set()

    def _take(candidate: IntelligenceItem) -> bool:
        if len(selected) >= limit:
            return False
        key = candidate.item_id or f"{candidate.source}:{candidate.title}"
        if key in seen_ids:
            return False
        seen_ids.add(key)
        selected.append(candidate)
        return True

    for item in matched:
        if sum(1 for s in selected if _is_symbol_news(s)) >= matched_cap:
            # 相关命中里继续收市场源；个股新闻已达上限则跳过
            if _is_symbol_news(item):
                continue
        if not _take(item):
            break

    market_pool = sorted(
        (item for item in items if not _is_symbol_news(item)),
        key=lambda x: x.published_at,
        reverse=True,
    )
    _fill_market_diversity(
        selected,
        market_pool,
        limit=limit,
        min_market_sources=min_market_sources,
        take=_take,
    )

    for item in market_pool:
        if len(selected) >= limit:
            break
        _take(item)

    for item in items:
        if len(selected) >= limit:
            break
        _take(item)

    return selected[:limit]


def build_brief(
    symbol: str,
    items: list[IntelligenceItem],
) -> IntelligenceBrief:
    """构建 IntelligenceBrief。"""
    sources = {item.source for item in items}
    corroboration = count_corroborations(items)
    headline = items[0].title if items else "暂无最新情报"
    return IntelligenceBrief(
        symbol=symbol,
        timestamp=datetime.now(),
        items=items,
        source_count=len(sources),
        corroboration_count=corroboration,
        headline=headline,
    )


def brief_to_key_events(brief: IntelligenceBrief) -> list[str]:
    """将摘要转为 key_events 字符串列表。"""
    lines: list[str] = []
    for item in brief.items[:8]:
        tags = ",".join(item.event_tags) if item.event_tags else "general"
        lines.append(f"[{item.source}|{tags}] {item.title}")
    if brief.corroboration_count:
        lines.append(f"corroboration_groups={brief.corroboration_count}")
    return lines


def score_keyword_sentiment(text: str) -> float:
    """规则情绪分 [-1, 1]。"""
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    total = pos + neg
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / total))


def compute_sentiment_scores(items: list[IntelligenceItem], brief: IntelligenceBrief) -> dict[str, float]:
    """计算 L2 各子分数。

    cross_validation：无印证组 = 0.5（中性未知）；有印证组则从 0.5 单调抬升。不进入 composite。
    fund_sentiment：暂无真实资金流源，固定 0。
    social_buzz：新闻条数，不进入 composite。
    composite：词面正负，范围 [-1, 1]。
    """
    if not items:
        return {
            "nlp_score": 0.0,
            "social_buzz": 0.0,
            "policy_risk": 0.0,
            "fund_sentiment": 0.0,
            "composite": 0.0,
            "cross_validation": 0.5,
        }

    texts = [f"{item.title} {item.content}" for item in items]
    nlp = sum(score_keyword_sentiment(text) for text in texts) / len(texts)
    policy_hits = sum(1 for item in items if "policy" in item.event_tags)
    policy_risk = min(1.0, policy_hits / max(len(items), 1))
    buzz = min(1.0, len(items) / DEFAULT_BRIEF_LIMIT)
    if brief.corroboration_count <= 0:
        cross_val = 0.5
    else:
        cross_val = min(1.0, 0.5 + brief.corroboration_count / 6.0)
    # 方向只来自词面正负。条数、印证、政策标签留在各自字段，避免「新闻多」变成看多。
    composite = max(-1.0, min(1.0, nlp))
    return {
        "nlp_score": nlp,
        "social_buzz": buzz,
        "policy_risk": policy_risk,
        "fund_sentiment": 0.0,
        "composite": composite,
        "cross_validation": cross_val,
    }


def _is_symbol_news(item: IntelligenceItem) -> bool:
    return item.source == SOURCE_STOCK_NEWS


def _fill_market_diversity(
    selected: list[IntelligenceItem],
    market_pool: list[IntelligenceItem],
    *,
    limit: int,
    min_market_sources: int,
    take,
) -> None:
    """尽量让 brief 覆盖至少 min_market_sources 个非 stock_news 源。"""
    if min_market_sources <= 0:
        return
    present = {item.source for item in selected if not _is_symbol_news(item)}
    for item in market_pool:
        if len(present) >= min_market_sources:
            break
        if len(selected) >= limit:
            break
        if item.source in present:
            continue
        if take(item):
            present.add(item.source)


def _build_keywords(symbol: str, market: MarketSnapshot | None) -> list[str]:
    keywords = [symbol]
    if market is not None:
        index_name = market.extra.get("index_name")
        if isinstance(index_name, str) and index_name:
            keywords.append(index_name)
        name = market.extra.get("name")
        if isinstance(name, str) and name and name not in keywords:
            keywords.append(name)
    return keywords


def _matches_keywords(item: IntelligenceItem, keywords: list[str]) -> bool:
    text = f"{item.title} {item.content} {item.symbol_hint}"
    return any(kw and kw in text for kw in keywords)
