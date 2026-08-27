"""第 2 层常量 — 情报源与关键词。"""
from __future__ import annotations

from typing import Final

SOURCE_CLS: Final[str] = "cls"
SOURCE_EASTMONEY: Final[str] = "eastmoney"
SOURCE_THS: Final[str] = "ths"
SOURCE_SINA: Final[str] = "sina"
SOURCE_STOCK_NEWS: Final[str] = "stock_news"

DEFAULT_GLOBAL_SOURCES: Final[tuple[str, ...]] = (
    SOURCE_CLS,
    SOURCE_EASTMONEY,
    SOURCE_THS,
    SOURCE_SINA,
)

SOURCE_TIER: Final[dict[str, int]] = {
    SOURCE_CLS: 1,
    SOURCE_EASTMONEY: 1,
    SOURCE_THS: 2,
    SOURCE_SINA: 2,
    SOURCE_STOCK_NEWS: 2,
}

MAX_ITEMS_PER_SOURCE: Final[int] = 50
DEFAULT_BRIEF_LIMIT: Final[int] = 20
# brief 配额：为非 stock_news 市场源预留名额，避免个股新闻挤掉多源快讯
BRIEF_MARKET_RESERVE: Final[int] = 6
BRIEF_MIN_MARKET_SOURCES: Final[int] = 2
CORROBORATION_WINDOW_MINUTES: Final[int] = 120
TITLE_MATCH_MIN_CHARS: Final[int] = 8

POSITIVE_KEYWORDS: Final[tuple[str, ...]] = (
    "利好",
    "上涨",
    "增持",
    "降息",
    "复苏",
    "突破",
    "涨停",
    "净流入",
    "降准",
    "刺激",
)

NEGATIVE_KEYWORDS: Final[tuple[str, ...]] = (
    "利空",
    "下跌",
    "减持",
    "制裁",
    "冲突",
    "战争",
    "暴跌",
    "跌停",
    "净流出",
    "加息",
    "调查",
    "处罚",
)

EVENT_TAG_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "geopolitical": ("伊朗", "以色列", "冲突", "战争", "制裁", "导弹", "地缘", "俄乌"),
    "policy": ("证监会", "国务院", "监管", "央行", "政策", "立案", "新规"),
    "macro": ("美联储", "加息", "降息", "GDP", "CPI", "非农", "汇率"),
    "commodity": ("黄金", "原油", "油价", "白银", "铜", "大宗商品"),
    "tech": ("芯片", "英伟达", "AI", "算力", "半导体", "扎克伯格", "Meta"),
}

ENTITY_KEYWORDS: Final[tuple[str, ...]] = (
    "沪深300",
    "中证500",
    "创业板",
    "科创50",
    "北向资金",
    "美联储",
    "央行",
    "黄金",
    "原油",
    "英伟达",
    "人工智能",
)
