"""因子库常量。权重不进入开仓分。"""
from __future__ import annotations

from typing import Final

DEGRADED_WEIGHT_FACTOR: Final[float] = 0.5
# 股票 registry apply 后 active+degraded 保底数量（权威值在 layer5_risk.constants）
MIN_LIVE_FACTORS: Final[int] = 6
FACTOR_STATE_FILENAME_ETF: Final[str] = "factor_registry_state_etf.json"
FACTOR_STATE_FILENAME_STOCK: Final[str] = "factor_registry_state_stock.json"
