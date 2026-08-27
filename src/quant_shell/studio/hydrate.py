"""把交易模型灌进本进程设置与策略配置。"""
from __future__ import annotations

import os

from quant_shell.plugin.profile import RiskProfile, StrategyProfile, ThresholdProfile
from quant_shell.studio.schema import TradingModel
from quant_shell.studio.store import load_active_model


def model_to_profile(model: TradingModel) -> StrategyProfile:
    return StrategyProfile(
        name=model.name,
        version="studio",
        description=model.summary or model.idea[:80],
        thresholds=ThresholdProfile(
            signal_threshold_moderate=model.entry.moderate_threshold,
            signal_threshold_strong=model.entry.strong_threshold,
            signal_moderate_buy_scale=model.entry.moderate_buy_scale,
        ),
        risk=RiskProfile(
            portfolio_max_drawdown=model.risk.max_drawdown,
            max_drawdown=model.risk.max_drawdown,
            single_stock_limit=model.risk.single_stock_limit,
        ),
    )


def apply_model_env(model: TradingModel) -> None:
    os.environ["MAX_DRAWDOWN"] = str(model.risk.max_drawdown)
    os.environ["PORTFOLIO_MAX_DRAWDOWN"] = str(model.risk.max_drawdown)
    os.environ["SINGLE_STOCK_LIMIT"] = str(model.risk.single_stock_limit)
    os.environ["TOTAL_POSITION_LIMIT"] = str(model.risk.total_position_limit)
    os.environ["SIGNAL_THRESHOLD_MODERATE"] = str(model.entry.moderate_threshold)
    os.environ["SIGNAL_THRESHOLD_STRONG"] = str(model.entry.strong_threshold)
    os.environ["SIGNAL_MODERATE_BUY_SCALE"] = str(model.entry.moderate_buy_scale)
    from quant_shell.config.settings import reload_settings

    reload_settings()


def hydrate_studio() -> TradingModel | None:
    """CLI / 管道启动时读取前端保存的模型。"""
    model = load_active_model()
    if model is None:
        return None
    apply_model_env(model)
    return model
