"""因子基础设施 — 注册表、引擎、用户加载；无内置 alpha。"""
from quant_shell.factors.engine import AlphaFactorEngine
from quant_shell.factors.factory import build_empty_registry
from quant_shell.factors.loader import load_factor_builder, resolve_factor_spec
from quant_shell.factors.registry import FactorCategory, FactorRegistry, FactorSpec, FactorStatus
from quant_shell.factors.state_store import FactorScope, load_registry, save_registry_state

__all__ = [
    "AlphaFactorEngine",
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
