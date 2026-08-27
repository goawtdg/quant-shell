"""Reference 策略插件 — 委托 policy.engine（与主线行为一致）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from quant_shell.execution.portfolio import PaperPortfolioStore
from reference_policy.policy.config import SleevePolicyConfig, load_policy_config
from reference_policy.policy.engine import StrategyPolicyEngine

if TYPE_CHECKING:
    from quant_shell.plugin.profile import StrategyProfile


class ReferencePolicyPlugin(StrategyPolicyEngine):
    """官方 reference：完整 L4 政策栈，配置来自 strategy.yaml 或 settings。"""

    @classmethod
    def from_profile(
        cls,
        profile: StrategyProfile,
        portfolio_store: PaperPortfolioStore | None = None,
        **_: object,
    ) -> ReferencePolicyPlugin:
        from quant_shell.plugin.profile import StrategyProfile as _Profile

        if not isinstance(profile, _Profile):
            raise TypeError("profile must be StrategyProfile")
        config = profile.to_policy_config()
        return cls(portfolio_store=portfolio_store, config=config)

    @classmethod
    def default(cls, portfolio_store: PaperPortfolioStore | None = None) -> ReferencePolicyPlugin:
        return cls(portfolio_store=portfolio_store, config=load_policy_config())
