"""硬风险码目录 — 框架 invariant；策略可派生，LLM 不得发明。"""
from __future__ import annotations

from enum import StrEnum


class HardCode(StrEnum):
    """定稿收紧用硬码；字符串唯一真相。"""

    MONITOR_CRITICAL = "MONITOR_CRITICAL"
    INTEL_REVIEW_HARD = "INTEL_REVIEW_HARD"
    STRATEGY_DEGRADED = "STRATEGY_DEGRADED"


HARD_CODE_VALUES: frozenset[str] = frozenset(c.value for c in HardCode)


def is_hard_code(flag: str) -> bool:
    """是否为硬风险码（精确匹配）。"""
    return str(flag).upper() in HARD_CODE_VALUES


def strip_hard_codes(flags: list[str]) -> list[str]:
    """去掉硬码，仅保留软叙述旗。"""
    return [f for f in flags if not is_hard_code(f)]
