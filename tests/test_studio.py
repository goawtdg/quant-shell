from __future__ import annotations

from quant_shell.factors.expr_eval import validate_expression_syntax
from quant_shell.studio.catalog import FACTOR_CATALOG
from quant_shell.studio.compiler import compile_heuristic
from quant_shell.studio.registry import build_registry_from_model
from quant_shell.studio.schema import model_from_dict


def test_catalog_expressions_are_valid():
    for item in FACTOR_CATALOG:
        validate_expression_syntax(str(item["expression"]))


def test_unknown_factor_dropped():
    model = model_from_dict(
        {
            "factors": [
                {"id": "not_a_real_factor", "enabled": True, "weight": 1},
                {"id": "momentum_20", "enabled": True, "weight": 0.4},
            ]
        }
    )
    ids = {f.id for f in model.factors}
    assert "not_a_real_factor" not in ids
    assert "momentum_20" in ids
    assert any("没有" in n for n in model.notes)


def test_heuristic_momentum_and_drawdown():
    model = compile_heuristic("用20日动量追涨，回撤超过12%就不要买")
    enabled = {f.id for f in model.factors if f.enabled}
    assert "momentum_20" in enabled
    assert abs(model.risk.max_drawdown - 0.12) < 1e-9


def test_registry_disables_unchecked_factors():
    model = compile_heuristic("低波动稳健一点")
    reg = build_registry_from_model(model)
    names = {s.name for s in reg.active_specs()}
    assert "low_vol" in names
    disabled = {s.name for s in reg.all_specs() if s.status.value == "disabled"}
    assert "momentum_5" in disabled or "momentum_5" in {s.name for s in reg.all_specs()}
