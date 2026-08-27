"""DeepSeek 分析师常量 — 行为阈值（非密钥）。"""
from __future__ import annotations

from typing import Final

MAX_ANALYST_SENTIMENT_ABS: Final[float] = 0.45
LOW_CONFIDENCE_THRESHOLD: Final[float] = 0.55
HUMAN_REVIEW_CONFIDENCE: Final[float] = 0.70

RULE_WEIGHT_IN_BLEND: Final[float] = 0.40
ANALYST_WEIGHT_IN_BLEND: Final[float] = 0.60

RECOMMENDED_ACTIONS: Final[tuple[str, ...]] = (
    "MONITOR",
    "REDUCE",
    "HUMAN_ONLY",
    "NEUTRAL",
    "INCREASE",
)

NOVELTY_LEVELS: Final[tuple[str, ...]] = (
    "known",
    "uncertain",
    "black_swan",
)
