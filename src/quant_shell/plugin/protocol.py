"""StrategyPlugin — 用户策略须满足的 StrategyEngine 契约。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from quant_shell.common.interfaces import StrategyEngine
from quant_shell.common.policy_types import PolicyVerdict
from quant_shell.common.types import DecisionContextPack, PipelineContext


@runtime_checkable
class StrategyPlugin(Protocol):
    """与 StrategyEngine 方法集一致的用户策略插件。"""

    def build_context_pack(self, ctx: PipelineContext) -> DecisionContextPack:
        ...

    def evaluate_policy(self, ctx: PipelineContext) -> PolicyVerdict:
        ...


def is_strategy_plugin(obj: object) -> bool:
    return isinstance(obj, StrategyEngine) or isinstance(obj, StrategyPlugin)
