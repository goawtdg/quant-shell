"""因子基础设施 — 注册表与用户加载。开仓分不在这里合成。"""
from quant_shell.factors.factory import build_empty_registry
from quant_shell.factors.loader import load_factor_builder, resolve_factor_spec
from quant_shell.factors.registry import FactorCategory, FactorRegistry, FactorSpec, FactorStatus
from quant_shell.factors.state_store import FactorScope, load_registry, save_registry_state

__all__ = [
    "FactorCategory",
    "FactorRegistry",
    "FactorScope",
    "FactorSpec",
    "FactorStatus",
    "build_empty_registry",
    "load_factor_builder",
    "load_registry",
    "resolve_factor_spec",
    "save_registry_state",
]
