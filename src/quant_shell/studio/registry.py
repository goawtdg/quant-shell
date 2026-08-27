"""根据当前交易模型组装 FactorRegistry。"""
from __future__ import annotations

from quant_shell.factors.expr_eval import make_compute
from quant_shell.factors.registry import FactorCategory, FactorRegistry, FactorSpec, FactorStatus
from quant_shell.studio.catalog import catalog_by_id
from quant_shell.studio.schema import TradingModel
from quant_shell.studio.store import load_active_model


def build_registry_from_model(model: TradingModel) -> FactorRegistry:
    catalog = catalog_by_id()
    registry = FactorRegistry()
    for pick in model.factors:
        item = catalog.get(pick.id)
        if item is None:
            continue
        try:
            category = FactorCategory(str(item["category"]))
        except ValueError:
            category = FactorCategory.COMPOSITE
        registry.register(
            FactorSpec(
                name=pick.id,
                category=category,
                description=str(item["label"]),
                weight=float(pick.weight),
                compute=make_compute(str(item["expression"])),
                status=FactorStatus.ACTIVE if pick.enabled else FactorStatus.DISABLED,
            )
        )
    return registry


def build_registry(scope: str = "etf") -> FactorRegistry:  # noqa: ARG001
    """FACTOR_MODULE 兼容入口；无激活模型则空表。"""
    model = load_active_model()
    if model is None:
        return FactorRegistry()
    return build_registry_from_model(model)
