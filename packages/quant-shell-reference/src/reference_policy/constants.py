"""第 4 层常量 — 选股资格。"""
from __future__ import annotations

from typing import Final

# 指南 §12.2 硬过滤
MIN_MARKET_CAP_YUAN: Final[float] = 5_000_000_000.0
MAX_PE_SANITY: Final[float] = 200.0
MIN_PE_SANITY: Final[float] = 0.0

# A 股追高防护（硬过滤 + 入场评估共用阈值）
MAX_RETURN_5D_GATE: Final[float] = 0.25
MAX_RETURN_10D_GATE: Final[float] = 0.35
MAX_RETURN_5D_ENTRY: Final[float] = 0.25
MAX_RETURN_10D_ENTRY: Final[float] = 0.35
RETURN_5D_DAYS: Final[int] = 5
RETURN_10D_DAYS: Final[int] = 10

DEFAULT_TOP_N: Final[int] = 20
DEFAULT_MAX_SYMBOLS: Final[int] = 0

STRATEGY_MULTI_FACTOR: Final[str] = "multi_factor_pick"
STRATEGY_INDEX_DCA: Final[str] = "index_dca"
