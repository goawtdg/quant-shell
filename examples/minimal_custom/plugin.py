"""最小自定义 — 继承 reference，仅 YAML 改阈值。"""
from __future__ import annotations

from quant_shell.plugin.profile import StrategyProfile
from reference_policy.policy.plugin import ReferencePolicyPlugin


class MinimalCustomPlugin(ReferencePolicyPlugin):
    @classmethod
    def from_profile(cls, profile: StrategyProfile, **kwargs: object) -> MinimalCustomPlugin:
        return super().from_profile(profile, **kwargs)
