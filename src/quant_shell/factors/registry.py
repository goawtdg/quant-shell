"""因子注册表 — 名称、类别、权重、计算函数。"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

import pandas as pd

from quant_shell.factors.constants import DEGRADED_WEIGHT_FACTOR


class FactorCategory(StrEnum):
    """因子类别。"""

    MOMENTUM = "momentum"
    REVERSAL = "reversal"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    OVERHEAT = "overheat"
    VALUE = "value"
    COMPOSITE = "composite"


class FactorStatus(StrEnum):
    """因子生命周期状态（Sprint C IC 监控用）。"""

    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"


FactorComputeFn = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class FactorSpec:
    """单个因子定义。"""

    name: str
    category: FactorCategory
    description: str
    weight: float
    compute: FactorComputeFn
    status: FactorStatus = FactorStatus.ACTIVE
    # 验证门禁最佳符号：+1 正向，-1 取反后使用（与 overheat 类固定反转正交）
    sign: float = 1.0


class FactorRegistry:
    """因子注册与查询。"""

    def __init__(self) -> None:
        self._specs: dict[str, FactorSpec] = {}

    def register(self, spec: FactorSpec) -> None:
        """注册因子。"""
        self._specs[spec.name] = spec

    def all_specs(self) -> list[FactorSpec]:
        """返回全部因子（含 DISABLED）。"""
        return list(self._specs.values())

    def active_specs(self) -> list[FactorSpec]:
        """返回非 DISABLED 因子列表。

        DEGRADED 仍视为 active；调用方应使用 ``effective_weight`` 半权。
        """
        return [s for s in self._specs.values() if s.status != FactorStatus.DISABLED]

    def set_status(self, name: str, status: FactorStatus) -> None:
        """更新因子生命周期状态。"""
        spec = self._specs[name]
        self._specs[name] = replace(spec, status=status)

    def set_sign(self, name: str, sign: float) -> None:
        """更新因子使用符号（仅允许 ±1）。"""
        normalized = -1.0 if float(sign) < 0 else 1.0
        spec = self._specs[name]
        self._specs[name] = replace(spec, sign=normalized)

    @staticmethod
    def effective_weight(spec: FactorSpec) -> float:
        """按状态返回有效权重。"""
        if spec.status == FactorStatus.DISABLED:
            return 0.0
        if spec.status == FactorStatus.DEGRADED:
            return spec.weight * DEGRADED_WEIGHT_FACTOR
        return spec.weight

    def get(self, name: str) -> FactorSpec:
        """按名称获取因子。"""
        return self._specs[name]
