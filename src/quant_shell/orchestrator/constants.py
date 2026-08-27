"""编排层常量 — 与具体策略包解耦。"""
from __future__ import annotations

from typing import Final

# 选股池候选规模（再由 linkage_stock_top_n 截断入场）
DEFAULT_PICK_TOP_N: Final[int] = 20
