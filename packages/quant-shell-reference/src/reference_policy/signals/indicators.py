"""纯数学指标计算 — 无 IO，仅 pandas/numpy。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_shell.common.exceptions import ValidationError
from reference_policy.signals.constants import (
    BOLL_PERIOD,
    BOLL_STD,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    RSI_PERIOD,
    SIGNAL_CLAMP_MAX,
    SIGNAL_CLAMP_MIN,
)
from reference_policy.signals.signal_profile import min_history_bars, resolve_ma_periods


def _clamp(value: float) -> float:
    """将数值限制在 [-1, 1]。"""
    return max(SIGNAL_CLAMP_MIN, min(SIGNAL_CLAMP_MAX, value))


def _validate_closes(closes: pd.Series) -> pd.Series:
    """校验收盘价序列。"""
    series = pd.to_numeric(closes, errors="coerce").dropna()
    need = min_history_bars()
    if len(series) < need:
        raise ValidationError(
            message=f"历史 K 线不足 {need} 根，当前 {len(series)}",
            suggestion="增大 L1 历史拉取窗口或检查 ETF 代码",
        )
    return series


def sma(series: pd.Series, period: int) -> pd.Series:
    """简单移动平均。

    Args:
        series: 价格序列。
        period: 窗口长度。

    Returns:
        SMA 序列。
    """
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """指数移动平均。"""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = RSI_PERIOD) -> float:
    """相对强弱指数（最新值）。

    Args:
        series: 收盘价序列。
        period: RSI 周期。

    Returns:
        最新 RSI，范围 [0, 100]。
    """
    closes = _validate_closes(series)
    delta = closes.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    value = float(rsi_series.iloc[-1])
    if np.isnan(value):
        return 100.0
    return value


def macd_histogram(series: pd.Series) -> float:
    """MACD 柱状图最新值（DIF - DEA）。"""
    closes = _validate_closes(series)
    dif = ema(closes, MACD_FAST) - ema(closes, MACD_SLOW)
    dea = dif.ewm(span=MACD_SIGNAL, adjust=False, min_periods=MACD_SIGNAL).mean()
    histogram = dif - dea
    return float(histogram.iloc[-1])


def bollinger_bands(
    series: pd.Series,
    period: int = BOLL_PERIOD,
    num_std: float = BOLL_STD,
) -> tuple[float, float, float]:
    """布林带（最新上/中/下轨）。"""
    closes = _validate_closes(series)
    middle = float(closes.rolling(period, min_periods=period).mean().iloc[-1])
    std = float(closes.rolling(period, min_periods=period).std().iloc[-1])
    upper = middle + num_std * std
    lower = middle - num_std * std
    return upper, middle, lower


def dual_ma_score(series: pd.Series) -> float:
    """双均线得分：金叉偏多，死叉偏空。"""
    closes = _validate_closes(series)
    fast_period, slow_period = resolve_ma_periods()
    fast = float(sma(closes, fast_period).iloc[-1])
    slow = float(sma(closes, slow_period).iloc[-1])
    if slow == 0:
        return 0.0
    spread = (fast - slow) / slow
    return _clamp(spread * 10)


def macd_score(series: pd.Series) -> float:
    """MACD 柱得分：按近期波动归一化。"""
    closes = _validate_closes(series)
    hist = macd_histogram(closes)
    scale = float(closes.pct_change().std() * closes.iloc[-1])
    if scale == 0 or np.isnan(scale):
        return _clamp(np.sign(hist))
    return _clamp(hist / scale)


def rsi_score(series: pd.Series) -> float:
    """RSI 得分：超卖为正，超买为负。"""
    value = rsi(series)
    if value <= RSI_OVERSOLD:
        return _clamp((RSI_OVERSOLD - value) / RSI_OVERSOLD)
    if value >= RSI_OVERBOUGHT:
        return _clamp(-(value - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT))
    return _clamp((50.0 - value) / 50.0)


def bollinger_score(series: pd.Series) -> float:
    """布林带得分：近下轨偏多，近上轨偏空。"""
    closes = _validate_closes(series)
    upper, middle, lower = bollinger_bands(closes)
    price = float(closes.iloc[-1])
    band_width = upper - lower
    if band_width <= 0:
        return 0.0
    if price <= lower:
        return 1.0
    if price >= upper:
        return -1.0
    return _clamp((middle - price) / (band_width / 2))
