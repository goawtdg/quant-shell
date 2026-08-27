"""动态加载 STRATEGY_MODULE=package.module:Class。"""
from __future__ import annotations

import importlib
import os
from typing import Any, Callable

from quant_shell.common.interfaces import StrategyEngine

DEFAULT_STRATEGY_MODULE = "reference_policy.policy.plugin:ReferencePolicyPlugin"
DEFAULT_COMMIT_MODULE = "reference_policy.policy.commit:commit_decision"
DEFAULT_PICKER_MODULE = "reference_policy.picker.engine:FactorStrategyEngine"

_REFERENCE_HINT = (
    "默认插件来自可选包 quant-shell-reference。"
    "安装: pip install 'quant-shell[reference]' "
    "或本地 pip install -e ./packages/quant-shell-reference；"
    "也可设置 STRATEGY_MODULE / PICKER_MODULE / COMMIT_MODULE 指向自有实现。"
)


def _import_module(module_path: str):
    try:
        return importlib.import_module(module_path)
    except ImportError as exc:
        if module_path.startswith("reference_policy"):
            raise ImportError(
                f"cannot import {module_path!r}: {exc}. {_REFERENCE_HINT}"
            ) from exc
        raise


def resolve_strategy_spec(spec: str | None = None) -> str:
    raw = (spec or os.getenv("STRATEGY_MODULE") or DEFAULT_STRATEGY_MODULE).strip()
    if ":" not in raw:
        raise ValueError(f"STRATEGY_MODULE must be 'module.path:ClassName', got {raw!r}")
    return raw


def load_callable(spec: str) -> Callable[..., Any]:
    """加载 ``module.path:name`` 可调用对象。"""
    raw = spec.strip()
    if ":" not in raw:
        raise ValueError(f"callable spec must be 'module.path:name', got {raw!r}")
    module_path, _, name = raw.partition(":")
    if not module_path or not name:
        raise ValueError(f"invalid callable spec: {raw!r}")
    mod = _import_module(module_path)
    obj = getattr(mod, name, None)
    if obj is None:
        raise ImportError(f"{name} not found in {module_path}")
    if not callable(obj):
        raise TypeError(f"{raw} is not callable")
    return obj


def load_strategy_class(spec: str | None = None) -> type[StrategyEngine]:
    resolved = resolve_strategy_spec(spec)
    module_path, _, class_name = resolved.partition(":")
    if not module_path or not class_name:
        raise ValueError(f"invalid STRATEGY_MODULE: {resolved!r}")
    mod = _import_module(module_path)
    cls = getattr(mod, class_name, None)
    if cls is None:
        raise ImportError(f"{class_name} not found in {module_path}")
    if not isinstance(cls, type):
        raise TypeError(f"{resolved} is not a class")
    return cls


def reference_installed() -> bool:
    """可选示例包是否可导入。"""
    try:
        importlib.import_module("reference_policy")
        return True
    except ImportError:
        return False
