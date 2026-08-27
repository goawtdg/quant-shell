"""StrategyProfile — strategy.yaml 声明式阈值。"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from quant_shell.plugin.policy_config import SleevePolicyConfig, load_policy_config


@dataclass(frozen=True)
class ThresholdProfile:
    signal_threshold_moderate: float | None = None
    signal_threshold_strong: float | None = None
    signal_moderate_buy_scale: float | None = None
    factor_min_coverage: float | None = None


@dataclass(frozen=True)
class RiskProfile:
    portfolio_max_drawdown: float | None = None
    single_stock_limit: float | None = None
    max_drawdown: float | None = None


@dataclass(frozen=True)
class StrategyProfile:
    name: str = "unnamed"
    version: str = "1"
    description: str = ""
    thresholds: ThresholdProfile = field(default_factory=ThresholdProfile)
    risk: RiskProfile = field(default_factory=RiskProfile)

    @classmethod
    def load(cls, path: str | Path) -> StrategyProfile:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"strategy profile not found: {p}")
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"strategy profile must be a mapping: {p}")
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StrategyProfile:
        th_raw = raw.get("thresholds") or {}
        rk_raw = raw.get("risk") or {}
        if not isinstance(th_raw, dict):
            raise ValueError("thresholds must be a mapping")
        if not isinstance(rk_raw, dict):
            raise ValueError("risk must be a mapping")
        return cls(
            name=str(raw.get("name") or "unnamed"),
            version=str(raw.get("version") or "1"),
            description=str(raw.get("description") or ""),
            thresholds=ThresholdProfile(
                **{k: th_raw[k] for k in th_raw if k in {f.name for f in fields(ThresholdProfile)}}
            ),
            risk=RiskProfile(
                **{k: rk_raw[k] for k in rk_raw if k in {f.name for f in fields(RiskProfile)}}
            ),
        )

    def to_policy_config(self) -> SleevePolicyConfig:
        base = load_policy_config()
        overrides: dict[str, Any] = {}
        for f in fields(self.thresholds):
            val = getattr(self.thresholds, f.name)
            if val is not None:
                overrides[f.name] = val
        if self.risk.single_stock_limit is not None:
            overrides["single_stock_limit"] = self.risk.single_stock_limit
        if not overrides:
            return base
        base_dict = {f.name: getattr(base, f.name) for f in fields(base)}
        base_dict.update(overrides)
        return SleevePolicyConfig(**base_dict)

    def risk_env_overrides(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.risk.portfolio_max_drawdown is not None:
            out["PORTFOLIO_MAX_DRAWDOWN"] = str(self.risk.portfolio_max_drawdown)
        if self.risk.max_drawdown is not None:
            out["MAX_DRAWDOWN"] = str(self.risk.max_drawdown)
        if self.risk.single_stock_limit is not None:
            out["SINGLE_STOCK_LIMIT"] = str(self.risk.single_stock_limit)
        return out
