"""第 3 层常量 — 指标参数与融合权重。"""
from __future__ import annotations

from typing import Final

# 双均线（长线 profile 见 signal_profile.py）
MA_FAST_PERIOD: Final[int] = 20
MA_SLOW_PERIOD: Final[int] = 60
MA_FAST_PERIOD_LONG: Final[int] = 60
MA_SLOW_PERIOD_LONG: Final[int] = 120

# MACD (12, 26, 9)
MACD_FAST: Final[int] = 12
MACD_SLOW: Final[int] = 26
MACD_SIGNAL: Final[int] = 9

# RSI
RSI_PERIOD: Final[int] = 14
RSI_OVERSOLD: Final[float] = 30.0
RSI_OVERBOUGHT: Final[float] = 70.0

# 布林带
BOLL_PERIOD: Final[int] = 20
BOLL_STD: Final[float] = 2.0

# 子指标权重（层内归一，合计 1.0）
MATH_WEIGHT_DUAL_MA: Final[float] = 0.30
MATH_WEIGHT_MACD: Final[float] = 0.25
MATH_WEIGHT_RSI: Final[float] = 0.25
MATH_WEIGHT_BOLLINGER: Final[float] = 0.20

# 历史默认权重。运行时以 settings 为准。
# 印证次数不再进入 opportunity，SIGNAL_WEIGHT_INTELLIGENCE 只保留给旧配置读取。
SIGNAL_WEIGHT_MATH: Final[float] = 0.40
SIGNAL_WEIGHT_SENTIMENT: Final[float] = 0.35
SIGNAL_WEIGHT_INTELLIGENCE: Final[float] = 0.25

# layer3 默认常量；运行时门槛以 settings（SIGNAL_THRESHOLD_*）为准
SIGNAL_THRESHOLD_STRONG: Final[float] = 0.7
SIGNAL_THRESHOLD_MODERATE: Final[float] = 0.4

SIGNAL_CLAMP_MIN: Final[float] = -1.0
SIGNAL_CLAMP_MAX: Final[float] = 1.0

MIN_HISTORY_BARS: Final[int] = MA_SLOW_PERIOD + 5

# adapter 时序适配
ADAPT_LOOKBACK: Final[int] = 60
WINSOR_LOWER: Final[float] = 0.01
WINSOR_UPPER: Final[float] = 0.99
