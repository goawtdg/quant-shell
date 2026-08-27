"""Alpha 因子库常量。"""
from __future__ import annotations

from typing import Final

from quant_shell.signals.constants import (
    SIGNAL_CLAMP_MAX as SCORE_CLAMP_MAX,
    SIGNAL_CLAMP_MIN as SCORE_CLAMP_MIN,
)

MIN_OHLCV_BARS: Final[int] = 65

MOMENTUM_PERIOD_SHORT: Final[int] = 5
MOMENTUM_PERIOD_MID: Final[int] = 20
MOMENTUM_PERIOD_LONG: Final[int] = 60
VOLATILITY_PERIOD: Final[int] = 20
VOLUME_MA_PERIOD: Final[int] = 20
MA_PERIOD: Final[int] = 20
RSI_PERIOD: Final[int] = 14
PE_UNDERVALUE_BLEND_DEFAULT: Final[float] = 0.35
PE_OVERVALUE_BLEND_DEFAULT: Final[float] = 0.65
VALUE_REGIME_BLEND_STRENGTH: Final[float] = 0.3

COMPOSITE_LOW_VOL_MOMENTUM_WEIGHT: Final[float] = 0.30

TECH_WEIGHT_IN_MATH: Final[float] = 0.45
ALPHA_WEIGHT_IN_MATH: Final[float] = 0.55

DEGRADED_WEIGHT_FACTOR: Final[float] = 0.5
# 股票 registry apply 后 active+degraded 保底数量（权威值在 layer5_risk.constants）
MIN_LIVE_FACTORS: Final[int] = 6
FACTOR_STATE_FILENAME_ETF: Final[str] = "factor_registry_state_etf.json"
FACTOR_STATE_FILENAME_STOCK: Final[str] = "factor_registry_state_stock.json"
