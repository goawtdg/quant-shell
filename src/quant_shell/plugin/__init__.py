"""策略插件：契约、配置、加载。"""
from quant_shell.plugin.loader import load_strategy_class, resolve_strategy_spec
from quant_shell.plugin.profile import StrategyProfile
from quant_shell.plugin.protocol import StrategyPlugin

__all__ = [
    "StrategyPlugin",
    "StrategyProfile",
    "load_strategy_class",
    "resolve_strategy_spec",
]
