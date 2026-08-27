"""第 4 层常量 — 选股阈值与权重。"""
from __future__ import annotations

from typing import Final

from quant_shell.data.constants import (
    INDEX_CODE_MAP,
    UNIVERSE_CSI300,
    UNIVERSE_CSI500,
)

# 指南 §12.2 硬过滤
MIN_MARKET_CAP_YUAN: Final[float] = 5_000_000_000.0
MIN_ROE: Final[float] = 0.10
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

# 截面合成：alpha 价量 vs 基本面
WEIGHT_ALPHA_FACTORS: Final[float] = 0.55
WEIGHT_FUNDAMENTAL: Final[float] = 0.45

WEIGHT_VALUE: Final[float] = 0.20
WEIGHT_QUALITY: Final[float] = 0.20
WEIGHT_MOMENTUM_3M: Final[float] = 0.25
WEIGHT_INDUSTRY_REL_MOM: Final[float] = 0.20
WEIGHT_LIQUIDITY: Final[float] = 0.15

STRATEGY_MULTI_FACTOR: Final[str] = "multi_factor_pick"
STRATEGY_INDEX_DCA: Final[str] = "index_dca"
