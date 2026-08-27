"""非编程用户可选的因子菜谱（白名单表达式，不是承诺 alpha）。"""
from __future__ import annotations

from typing import Any

from quant_shell.factors.registry import FactorCategory

# expression 走 quant_shell.factors.expr_eval 白名单
FACTOR_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "momentum_20",
        "label": "20日动量",
        "hint": "最近涨得多的，倾向继续看多",
        "expression": "pct_change(close, 20)",
        "category": FactorCategory.MOMENTUM.value,
        "default_weight": 0.30,
    },
    {
        "id": "momentum_5",
        "label": "5日动量",
        "hint": "更短周期的涨跌方向",
        "expression": "pct_change(close, 5)",
        "category": FactorCategory.MOMENTUM.value,
        "default_weight": 0.15,
    },
    {
        "id": "low_vol",
        "label": "低波动",
        "hint": "波动越小分数越高（适合稳健）",
        "expression": "neg(std(pct_change(close), 20))",
        "category": FactorCategory.VOLATILITY.value,
        "default_weight": 0.20,
    },
    {
        "id": "volume_ratio",
        "label": "放量",
        "hint": "成交量相对近20日均量",
        "expression": "div(volume, sma(volume, 20))",
        "category": FactorCategory.LIQUIDITY.value,
        "default_weight": 0.15,
    },
    {
        "id": "ma_deviation",
        "label": "均线偏离",
        "hint": "价格相对20日均线的远近",
        "expression": "sub(div(close, sma(close, 20)), 1)",
        "category": FactorCategory.MOMENTUM.value,
        "default_weight": 0.20,
    },
)


def catalog_by_id() -> dict[str, dict[str, Any]]:
    return {str(item["id"]): item for item in FACTOR_CATALOG}


def catalog_public() -> list[dict[str, Any]]:
    """前端展示用（不含内部求值细节以外的字段）。"""
    return [
        {
            "id": item["id"],
            "label": item["label"],
            "hint": item["hint"],
            "category": item["category"],
            "default_weight": item["default_weight"],
        }
        for item in FACTOR_CATALOG
    ]


def known_factor_ids() -> frozenset[str]:
    return frozenset(catalog_by_id())
