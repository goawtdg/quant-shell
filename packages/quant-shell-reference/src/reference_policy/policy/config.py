"""Re-export — canonical config lives in quant_shell.plugin.policy_config."""
from quant_shell.plugin.policy_config import SleevePolicyConfig, load_policy_config

__all__ = ["SleevePolicyConfig", "load_policy_config"]
