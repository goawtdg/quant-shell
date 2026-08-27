"""FACTOR_MODULE=pkg.mod:build_registry 动态加载用户因子。"""
from __future__ import annotations

import importlib
import os


def resolve_factor_spec() -> str | None:
    raw = os.getenv("FACTOR_MODULE", "").strip()
    return raw or None


def load_factor_builder(spec: str | None = None):
    resolved = spec or resolve_factor_spec()
    if not resolved:
        return None
    if ":" not in resolved:
        raise ValueError(f"FACTOR_MODULE must be 'module:build_registry', got {resolved!r}")
    module_path, _, fn_name = resolved.partition(":")
    mod = importlib.import_module(module_path)
    fn = getattr(mod, fn_name or "build_registry", None)
    if fn is None or not callable(fn):
        raise ImportError(f"{resolved} is not callable")
    return fn
