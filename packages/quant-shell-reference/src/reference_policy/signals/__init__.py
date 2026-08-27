"""Reference 信号 — 重导出框架 L3（策略侧可选用）。"""
from quant_shell.factors.engine import AlphaFactorEngine
from quant_shell.factors.factory import build_empty_registry as build_default_registry
from quant_shell.signals.fusion import SignalFusionGenerator

__all__ = ["AlphaFactorEngine", "SignalFusionGenerator", "build_default_registry"]
