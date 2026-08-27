"""全局常量 — 禁止在业务代码中使用魔法字符串。"""
from __future__ import annotations

from enum import StrEnum


class LayerId(StrEnum):
    """流水线层标识。"""

    L1_DATA = "L1_data"
    L2_INTELLIGENCE = "L2_intelligence"
    L3_SIGNALS = "L3_signals"
    L4_STRATEGY = "L4_strategy"
    L5_RISK = "L5_risk"
    L6_EXECUTION = "L6_execution"
    L7_AI_REASON = "L7_ai_reason"
    L7_HUMAN = "L7_human"


class LayerStatus(StrEnum):
    """层执行状态。"""

    OK = "ok"
    PLACEHOLDER = "placeholder"
    BLOCKED = "blocked"
    ERROR = "error"
    SIMULATED = "simulated"


class EvaluationMode(StrEnum):
    """流水线评估模式 — 入场或持仓重评。"""

    ENTRY = "entry"
    HOLD = "hold"


class RiskViolation(StrEnum):
    """L5 硬风控违规码。"""

    NO_CONTEXT_PACK = "NO_CONTEXT_PACK"
    DRAWDOWN_BREACH = "DRAWDOWN_BREACH"
    PORTFOLIO_DRAWDOWN_BREACH = "PORTFOLIO_DRAWDOWN_BREACH"
    TOTAL_POSITION_LIMIT = "TOTAL_POSITION_LIMIT"
    FACTOR_HEALTH_CRITICAL = "FACTOR_HEALTH_CRITICAL"
    ENTRY_NOT_ELIGIBLE = "ENTRY_NOT_ELIGIBLE"
    ADD_TO_POSITION_BLOCKED = "ADD_TO_POSITION_BLOCKED"
    SLEEVE_BLOCKED = "SLEEVE_BLOCKED"


class RiskAction(StrEnum):
    """风控裁决动作。"""

    EXECUTE = "EXECUTE"
    BLOCK = "BLOCK"


class MarketRegime(StrEnum):
    """市场环境。"""

    WEAK_BULL = "weak_bull"
    CONSOLIDATION = "consolidation"


STRATEGY_DEGRADATION_THRESHOLD = -0.30  # 默认；运行时以 settings.strategy_degradation_threshold 为准

DEFAULT_ORDER_QUANTITY = 100.0
