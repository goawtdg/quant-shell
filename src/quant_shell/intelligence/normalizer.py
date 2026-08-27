"""时间、文本与 ID 归一化。"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time

from quant_shell.common.types import IntelligenceItem


def normalize_text(text: str) -> str:
    """清理 HTML 与空白。"""
    cleaned = re.sub(r"<[^>]+>", "", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def make_item_id(source: str, title: str, published_at: datetime) -> str:
    """生成稳定 item_id。"""
    raw = f"{source}|{title[:80]}|{published_at.isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def parse_published(value: object, fallback: datetime | None = None) -> datetime:
    """解析多种时间格式。"""
    now = fallback or datetime.now()
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    text = str(value).strip()
    if not text:
        return now
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%H:%M:%S":
                return datetime.combine(now.date(), parsed.time())
            return parsed
        except ValueError:
            continue
    return now


def merge_title_content(title: str, content: str) -> tuple[str, str]:
    """补全缺失标题或正文。"""
    title_clean = normalize_text(title)
    content_clean = normalize_text(content)
    if not title_clean and content_clean:
        title_clean = content_clean[:48]
    if not content_clean:
        content_clean = title_clean
    return title_clean, content_clean


def build_item(
    *,
    source: str,
    source_tier: int,
    title: str,
    content: str,
    published_at: datetime,
    url: str = "",
    symbol_hint: str = "",
    importance: str = "",
) -> IntelligenceItem:
    """构建 IntelligenceItem。"""
    title_clean, content_clean = merge_title_content(title, content)
    return IntelligenceItem(
        item_id=make_item_id(source, title_clean, published_at),
        source=source,
        source_tier=source_tier,
        title=title_clean,
        content=content_clean,
        published_at=published_at,
        url=url,
        symbol_hint=symbol_hint,
        importance=importance,
    )
