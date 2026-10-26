"""策略侧入口。信号计算只在 quant_shell.signals，这里只重导出。"""
from quant_shell.factors.factory import build_empty_registry as build_default_registry
from quant_shell.signals.fusion import SignalFusionGenerator

__all__ = ["SignalFusionGenerator", "build_default_registry"]
