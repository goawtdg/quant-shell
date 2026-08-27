"""quant-shell — 独立量化框架壳层。"""
from quant_shell.factory import (
    create_commit_decision,
    create_signal_generator,
    create_strategy_engine,
    plugin_status,
)
from quant_shell.plugin.profile import StrategyProfile
from quant_shell.plugin.loader import load_strategy_class, resolve_strategy_spec

__all__ = [
    "StrategyProfile",
    "create_commit_decision",
    "create_signal_generator",
    "create_strategy_engine",
    "load_strategy_class",
    "plugin_status",
    "resolve_strategy_spec",
]

__version__ = "0.4.0"


def __getattr__(name: str):
    if name == "TradingPipeline":
        from quant_shell.orchestrator.pipeline import TradingPipeline

        return TradingPipeline
    if name == "PaperTradingPipeline":
        from quant_shell.orchestrator.paper_pipeline import PaperTradingPipeline

        return PaperTradingPipeline
    if name == "FullLinkageOrchestrator":
        from quant_shell.orchestrator.full_linkage import FullLinkageOrchestrator

        return FullLinkageOrchestrator
    if name == "build_linkage_parser":
        from quant_shell.orchestrator.run_cli import build_parser as build_linkage_parser

        return build_linkage_parser
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
