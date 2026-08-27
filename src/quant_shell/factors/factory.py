"""因子注册表 — 框架默认空表，由用户 FACTOR_MODULE 注入。"""
from __future__ import annotations

from quant_shell.factors.registry import FactorRegistry


def build_empty_registry() -> FactorRegistry:
    """框架不包含任何内置 alpha；用户通过 FACTOR_MODULE 或 JSON 插件注册。"""
    return FactorRegistry()
