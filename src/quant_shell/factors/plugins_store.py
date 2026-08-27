"""因子插件持久化 — 与 registry state 分文件。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from quant_shell.factors.expr_eval import (
    ExprError,
    make_compute,
    validate_expression_syntax,
)
from quant_shell.factors.registry import (
    FactorCategory,
    FactorRegistry,
    FactorSpec,
    FactorStatus,
)

FactorScope = Literal["etf", "stock"]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
_SCHEMA_VERSION = "1.0"


def plugins_path(base_dir: Path, scope: FactorScope) -> Path:
    return base_dir / f"factor_plugins_{scope}.json"


def load_plugin_docs(base_dir: Path, scope: FactorScope) -> dict[str, Any]:
    path = plugins_path(base_dir, scope)
    if not path.exists():
        return {"schema_version": _SCHEMA_VERSION, "factors": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"corrupt plugins file: {path}")
    factors = raw.get("factors")
    if not isinstance(factors, list):
        raise ValueError(f"plugins factors must be list: {path}")
    return {
        "schema_version": str(raw.get("schema_version") or _SCHEMA_VERSION),
        "factors": factors,
    }


def save_plugin_docs(base_dir: Path, scope: FactorScope, doc: dict[str, Any]) -> Path:
    path = plugins_path(base_dir, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "factors": list(doc.get("factors") or []),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def plugin_names(base_dir: Path, scope: FactorScope) -> set[str]:
    doc = load_plugin_docs(base_dir, scope)
    names: set[str] = set()
    for item in doc["factors"]:
        if isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    return names


def register_plugins(registry: FactorRegistry, base_dir: Path, scope: FactorScope) -> int:
    """将插件因子合并进 registry；返回注册数量。"""
    doc = load_plugin_docs(base_dir, scope)
    count = 0
    for item in doc["factors"]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        expression = str(item.get("expression") or "").strip()
        if not name or not expression:
            continue
        try:
            category = FactorCategory(str(item.get("category") or "composite"))
        except ValueError:
            category = FactorCategory.COMPOSITE
        weight = float(item.get("weight") or 0.05)
        desc = str(item.get("description") or expression[:80])
        registry.register(
            FactorSpec(
                name=name,
                category=category,
                description=desc,
                weight=weight,
                compute=make_compute(expression),
                status=FactorStatus.DISABLED,
            )
        )
        count += 1
    return count


def add_plugin(
    base_dir: Path,
    scope: FactorScope,
    *,
    name: str,
    expression: str,
    description: str = "",
    category: str = "composite",
    weight: float = 0.05,
    builtin_names: set[str],
) -> dict[str, Any]:
    """校验并写入插件；强制 disabled。"""
    name = name.strip().lower()
    expression = expression.strip()
    if not _NAME_RE.match(name):
        raise ValueError("name must match ^[a-z][a-z0-9_]{1,62}$")
    if name in builtin_names:
        raise ValueError(f"name conflicts with builtin: {name}")
    try:
        validate_expression_syntax(expression)
    except ExprError as exc:
        raise ValueError(f"invalid expression: {exc}") from exc
    try:
        FactorCategory(category)
    except ValueError as exc:
        raise ValueError(f"invalid category: {category}") from exc

    doc = load_plugin_docs(base_dir, scope)
    factors = [f for f in doc["factors"] if isinstance(f, dict)]
    if any(str(f.get("name")) == name for f in factors):
        raise ValueError(f"plugin already exists: {name}")
    entry = {
        "name": name,
        "expression": expression,
        "description": description or expression[:80],
        "category": category,
        "weight": float(weight),
        "source": "plugin",
    }
    factors.append(entry)
    doc["factors"] = factors
    save_plugin_docs(base_dir, scope, doc)
    return entry


def delete_plugin(base_dir: Path, scope: FactorScope, name: str) -> None:
    """删除插件；不存在则 KeyError。"""
    doc = load_plugin_docs(base_dir, scope)
    factors = [f for f in doc["factors"] if isinstance(f, dict)]
    kept = [f for f in factors if str(f.get("name")) != name]
    if len(kept) == len(factors):
        raise KeyError(name)
    doc["factors"] = kept
    save_plugin_docs(base_dir, scope, doc)
