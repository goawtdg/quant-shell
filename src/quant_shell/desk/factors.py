"""因子列表 / 插件 — 本仓 registry + studio catalog。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from quant_shell.common.atomic_io import append_text
from quant_shell.desk.paths import data_dir, factor_audit_path
from quant_shell.factors.plugins_store import (
    add_plugin,
    delete_plugin,
    load_plugin_docs,
    plugin_names,
)
from quant_shell.factors.registry import FactorRegistry, FactorStatus
from quant_shell.factors.state_store import load_registry, save_registry_state
from quant_shell.studio.catalog import catalog_public
from quant_shell.studio.registry import build_registry_from_model
from quant_shell.studio.store import load_active_model


def _audit(event: str, **data: Any) -> None:
    path = factor_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now().isoformat(),
        "event": event,
        **data,
    }
    append_text(path, json.dumps(row, ensure_ascii=False) + "\n")


def list_factors(scope: str = "etf") -> dict[str, Any]:
    if scope not in ("etf", "stock"):
        raise ValueError("scope must be etf|stock")
    root = data_dir()
    registry = load_registry(base_dir=root, scope=scope)  # type: ignore[arg-type]
    model = load_active_model()
    if model is not None and scope == "etf":
        studio_reg = build_registry_from_model(model)
        for spec in studio_reg.all_specs():
            if spec.name not in {s.name for s in registry.all_specs()}:
                registry.register(spec)

    plugins = plugin_names(root, scope)  # type: ignore[arg-type]
    expr_by_name = {
        str(item.get("name")): str(item.get("expression") or "")
        for item in load_plugin_docs(root, scope)["factors"]  # type: ignore[arg-type]
        if isinstance(item, dict)
    }
    catalog_ids = {c["id"] for c in catalog_public()}
    factors: list[dict[str, Any]] = []
    counts = {"active": 0, "degraded": 0, "disabled": 0}
    for spec in registry.all_specs():
        status = spec.status.value
        counts[status] = counts.get(status, 0) + 1
        if spec.name in plugins:
            source = "plugin"
        elif spec.name in catalog_ids:
            source = "catalog"
        else:
            source = "builtin"
        row: dict[str, Any] = {
            "name": spec.name,
            "category": spec.category.value,
            "description": spec.description,
            "weight": spec.weight,
            "effective_weight": FactorRegistry.effective_weight(spec),
            "status": status,
            "source": source,
        }
        if source == "plugin":
            row["expression"] = expr_by_name.get(spec.name, "")
        factors.append(row)
    factors.sort(key=lambda f: (f["category"], f["name"]))
    return {
        "scope": scope,
        "counts": counts,
        "factors": factors,
        "meta": {},
        "builtin_count": len(catalog_ids),
        "plugin_count": len(plugins),
        "catalog": catalog_public(),
        "empty": len(factors) == 0,
    }


def create_plugin_factor(
    *,
    scope: str,
    name: str,
    expression: str,
    description: str = "",
    category: str = "composite",
    weight: float = 0.05,
) -> dict[str, Any]:
    if scope not in ("etf", "stock"):
        raise ValueError("scope must be etf|stock")
    root = data_dir()
    catalog_ids = {c["id"] for c in catalog_public()}
    entry = add_plugin(
        root,
        scope,  # type: ignore[arg-type]
        name=name,
        expression=expression,
        description=description,
        category=category,
        weight=weight,
        builtin_names=catalog_ids,
    )
    _audit("create_plugin", scope=scope, name=name)
    return {"ok": True, "factor": entry}


def delete_plugin_factor(scope: str, name: str) -> dict[str, Any]:
    if scope not in ("etf", "stock"):
        raise ValueError("scope must be etf|stock")
    root = data_dir()
    delete_plugin(root, scope, name)  # type: ignore[arg-type]
    _audit("delete_plugin", scope=scope, name=name)
    return {"ok": True, "name": name}


def update_factor_status(
    scope: str,
    name: str,
    status: str,
    reason: str,
) -> dict[str, Any]:
    if scope not in ("etf", "stock"):
        raise ValueError("scope must be etf|stock")
    try:
        st = FactorStatus(status)
    except ValueError as exc:
        raise ValueError("status must be active|degraded|disabled") from exc
    root = data_dir()
    registry = load_registry(base_dir=root, scope=scope)  # type: ignore[arg-type]
    names = {s.name for s in registry.all_specs()}
    if name not in names:
        raise KeyError(name)
    registry.set_status(name, st)
    save_registry_state(registry, base_dir=root, scope=scope)  # type: ignore[arg-type]
    _audit("patch_status", scope=scope, name=name, status=status, reason=reason)
    return {"ok": True, "name": name, "status": status}
