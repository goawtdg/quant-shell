"""第 5 层常量 — IC 监控与风险阈值。"""
from __future__ import annotations

from typing import Final

IC_LOOKBACK_DAYS: Final[int] = 60
IC_LONG_LOOKBACK_DAYS: Final[int] = 120
FORWARD_RETURN_DAYS: Final[int] = 5
MIN_IC_SAMPLES: Final[int] = 30

# 股票门禁：双窗 fail 连续次数达此值才 hard-disable
FAIL_STREAK_TO_DISABLE: Final[int] = 2
# apply 后 active+degraded 保底数量
MIN_LIVE_FACTORS: Final[int] = 6
# degraded 半权池上限（超出按 signed IR 淘汰）
# 8 过严会在弱市把书砍到开不出单；20 ≈ 可回到「约二十个活因子」厚度，
# 仍保留 Top-K（最弱 review 继续 disable），不等于全员满权
MAX_DEGRADED_FACTORS: Final[int] = 20

IC_DEGRADED_THRESHOLD: Final[float] = 0.02
IC_DISABLED_THRESHOLD: Final[float] = 0.0
IC_RECOVERY_THRESHOLD: Final[float] = 0.03

LIVE_SHARPE_WINDOW: Final[int] = 30
BACKTEST_SHARPE_WINDOW: Final[int] = 120
VAR_CONFIDENCE: Final[float] = 0.95
