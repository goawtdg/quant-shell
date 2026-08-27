"""第 5 层风险指标计算 — Sprint C 接入历史收益。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_shell.common.types import RiskMetrics
from quant_shell.config.settings import settings
from quant_shell.risk.constants import (
    BACKTEST_SHARPE_WINDOW,
    LIVE_SHARPE_WINDOW,
    VAR_CONFIDENCE,
)


class MetricsCalculator:
    """Sharpe、最大回撤、VaR 等指标计算器。"""

    @staticmethod
    def daily_returns(close: pd.Series) -> np.ndarray:
        """日收益率数组。"""
        returns = pd.to_numeric(close, errors="coerce").pct_change().dropna()
        return returns.to_numpy(dtype=float)

    @staticmethod
    def sharpe(returns: np.ndarray, risk_free: float | None = None) -> float:
        """计算年化 Sharpe 比率。

        Args:
            returns: 日收益率序列。
            risk_free: 无风险利率，默认取 settings。

        Returns:
            年化 Sharpe，数据不足时返回 0。
        """
        rate = settings.risk_free_rate if risk_free is None else risk_free
        if len(returns) < 2:
            return 0.0
        excess = returns - rate / 252
        std = excess.std()
        if std == 0:
            return 0.0
        return float(excess.mean() / std * np.sqrt(252))

    @staticmethod
    def sortino(returns: np.ndarray, risk_free: float | None = None) -> float:
        """年化 Sortino 比率。"""
        rate = settings.risk_free_rate if risk_free is None else risk_free
        if len(returns) < 2:
            return 0.0
        excess = returns - rate / 252
        downside = excess[excess < 0]
        if len(downside) == 0:
            return 0.0
        downside_std = downside.std()
        if downside_std == 0:
            return 0.0
        return float(excess.mean() / downside_std * np.sqrt(252))

    @staticmethod
    def max_drawdown(equity_curve: np.ndarray) -> float:
        """计算最大回撤。

        Args:
            equity_curve: 净值曲线。

        Returns:
            最大回撤比例 [0, 1]。
        """
        if len(equity_curve) == 0:
            return 0.0
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (peak - equity_curve) / np.where(peak == 0, 1, peak)
        return float(drawdown.max())

    @staticmethod
    def current_drawdown(equity_curve: np.ndarray) -> float:
        """当前回撤（相对历史峰值）。"""
        if len(equity_curve) == 0:
            return 0.0
        peak = float(np.max(equity_curve))
        if peak == 0:
            return 0.0
        return float((peak - equity_curve[-1]) / peak)

    @staticmethod
    def var_historical(returns: np.ndarray, confidence: float = VAR_CONFIDENCE) -> float:
        """历史 VaR（正数表示损失比例）。"""
        if len(returns) < 5:
            return 0.0
        quantile = 1.0 - confidence
        loss = float(-np.quantile(returns, quantile))
        return max(0.0, loss)

    @staticmethod
    def volatility_annual(returns: np.ndarray) -> float:
        """年化波动率。"""
        if len(returns) < 2:
            return 0.0
        return float(returns.std() * np.sqrt(252))

    @staticmethod
    def win_rate(returns: np.ndarray) -> float:
        """胜率。"""
        if len(returns) == 0:
            return 0.0
        return float((returns > 0).sum() / len(returns))

    @staticmethod
    def profit_loss_ratio(returns: np.ndarray) -> float:
        """盈亏比（平均盈利 / 平均亏损）。"""
        gains = returns[returns > 0]
        losses = returns[returns < 0]
        if len(gains) == 0 or len(losses) == 0:
            return 0.0
        avg_gain = float(gains.mean())
        avg_loss = float(abs(losses.mean()))
        if avg_loss == 0:
            return 0.0
        return avg_gain / avg_loss

    @classmethod
    def build_risk_metrics(cls, ohlcv: pd.DataFrame) -> RiskMetrics:
        """从 OHLCV 构建完整 RiskMetrics。"""
        close = pd.to_numeric(ohlcv["close"], errors="coerce").dropna()
        returns = cls.daily_returns(close)
        equity = (1 + pd.Series(returns)).cumprod().to_numpy()
        return RiskMetrics(
            sharpe_ratio=cls.sharpe(returns),
            sortino_ratio=cls.sortino(returns),
            max_drawdown=cls.max_drawdown(equity),
            current_drawdown=cls.current_drawdown(equity),
            var_95_1d=cls.var_historical(returns),
            volatility_annual=cls.volatility_annual(returns),
            win_rate=cls.win_rate(returns),
            profit_loss_ratio=cls.profit_loss_ratio(returns),
        )

    @classmethod
    def live_and_backtest_sharpe(cls, ohlcv: pd.DataFrame) -> tuple[float, float]:
        """近 30 日 vs 全样本 Sharpe。"""
        close = pd.to_numeric(ohlcv["close"], errors="coerce").dropna()
        returns = cls.daily_returns(close)
        live = returns[-LIVE_SHARPE_WINDOW:] if len(returns) >= LIVE_SHARPE_WINDOW else returns
        backtest = (
            returns[-BACKTEST_SHARPE_WINDOW:]
            if len(returns) >= BACKTEST_SHARPE_WINDOW
            else returns
        )
        return cls.sharpe(live), cls.sharpe(backtest)
