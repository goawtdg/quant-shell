"""因子注册表状态持久化 — ETF / 股票双轨 scope。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from quant_shell.common.atomic_io import write_text_atomic
from quant_shell.common.logging_config import get_logger
from quant_shell.config.env_loader import project_root
from quant_shell.factors.constants import (
    FACTOR_STATE_FILENAME_ETF,
    FACTOR_STATE_FILENAME_STOCK,
    MIN_LIVE_FACTORS,
)
from quant_shell.factors.factory import build_empty_registry
from quant_shell.factors.loader import load_factor_builder
from quant_shell.factors.registry import FactorRegistry, FactorStatus

logger = get_logger(__name__)

FactorScope = Literal["etf", "stock"]

_SCOPE_FILENAMES: dict[FactorScope, str] = {
    "etf": FACTOR_STATE_FILENAME_ETF,
    "stock": FACTOR_STATE_FILENAME_STOCK,
}


def default_state_dir() -> Path:
    return project_root() / "data"


def state_file_path(
    base_dir: Path | None = None,
    scope: FactorScope = "etf",
) -> Path:
    root = base_dir or default_state_dir()
    return root / _SCOPE_FILENAMES[scope]


def _parse_status_payload(payload: object) -> dict[str, str]:
    if isinstance(payload, dict) and "status" in payload:
        inner = payload["status"]
        if isinstance(inner, dict):
            return {str(k): str(v) for k, v in inner.items()}
    if isinstance(payload, dict):
        return {str(k): str(v) for k, v in payload.items()}
    return {}


def _apply_status_map(registry: FactorRegistry, status_map: dict[str, str]) -> None:
    for name, status_value in status_map.items():
        try:
            status = FactorStatus(str(status_value))
            registry.set_status(name, status)
        except (ValueError, KeyError):
            logger.warning("load_registry skip unknown factor=%s", name)


def _apply_sign_map(registry: FactorRegistry, signs: object) -> None:
    if not isinstance(signs, dict):
        return
    for name, value in signs.items():
        try:
            registry.set_sign(str(name), float(value))
        except (ValueError, KeyError, TypeError):
            logger.warning("load_registry skip sign factor=%s", name)


def _merge_registry(base: FactorRegistry, other: FactorRegistry) -> None:
    for spec in other.all_specs():
        base.register(spec)


def load_registry(
    base_dir: Path | None = None,
    scope: FactorScope = "etf",
) -> FactorRegistry:
    """空表 + 用户 FACTOR_MODULE + JSON 表达式插件 + 持久化状态。"""
    from quant_shell.factors.plugins_store import register_plugins

    root = base_dir or default_state_dir()
    registry = build_empty_registry()

    builder = load_factor_builder()
    if builder is not None:
        try:
            user_reg = builder(scope=scope)
        except TypeError:
            user_reg = builder()
        if not isinstance(user_reg, FactorRegistry):
            raise TypeError("FACTOR_MODULE must return FactorRegistry")
        _merge_registry(registry, user_reg)
    else:
        from quant_shell.config.env_loader import project_root
        from quant_shell.studio.registry import build_registry_from_model
        from quant_shell.studio.store import load_active_model

        if root.resolve() == (project_root() / "data").resolve():
            studio = load_active_model()
            if studio is not None:
                _merge_registry(registry, build_registry_from_model(studio))

    register_plugins(registry, root, scope)

    path = state_file_path(root, scope)
    if not path.exists():
        _warn_stale_validation(root, scope)
        return registry

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("load_registry scope=%s skip corrupt state err=%s", scope, exc)
        return registry

    _apply_status_map(registry, _parse_status_payload(payload))
    if isinstance(payload, dict) and isinstance(payload.get("meta"), dict):
        _apply_sign_map(registry, payload["meta"].get("signs"))
    _warn_stale_validation(root, scope, payload if isinstance(payload, dict) else None)
    return registry


def _warn_stale_validation(
    root: Path,
    scope: FactorScope,
    payload: dict[str, object] | None = None,
) -> None:
    from quant_shell.risk.factor_validation import warn_if_validation_stale

    evaluated_at: object | None = None
    if scope == "stock":
        if payload and isinstance(payload.get("meta"), dict):
            evaluated_at = payload["meta"].get("evaluated_at")  # type: ignore[union-attr]
        if evaluated_at is None:
            evaluated_at = load_registry_meta(root, scope).get("evaluated_at")
        report_path = root / "factor_validation" / "latest.json"
    else:
        report_path = root / "factor_validation_etf" / "latest.json"

    if evaluated_at is None and report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(report, dict):
                evaluated_at = report.get("evaluated_at")
        except (json.JSONDecodeError, OSError):
            evaluated_at = None

    warn_if_validation_stale(evaluated_at, scope=scope)


def load_registry_meta(
    base_dir: Path | None = None,
    scope: FactorScope = "stock",
) -> dict[str, object]:
    path = state_file_path(base_dir, scope)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("load_registry_meta scope=%s skip corrupt err=%s", scope, exc)
        return {}
    if isinstance(payload, dict) and "meta" in payload and isinstance(payload["meta"], dict):
        return dict(payload["meta"])
    return {}


def save_registry_state(
    registry: FactorRegistry,
    base_dir: Path | None = None,
    scope: FactorScope = "etf",
    meta: dict[str, object] | None = None,
) -> None:
    path = state_file_path(base_dir, scope)
    path.parent.mkdir(parents=True, exist_ok=True)
    status_payload = {spec.name: spec.status.value for spec in registry.all_specs()}
    if scope == "stock" and meta is not None:
        signs = {spec.name: int(spec.sign) for spec in registry.all_specs()}
        merged = dict(meta)
        merged.setdefault("signs", signs)
        merged.setdefault("min_live_factors", MIN_LIVE_FACTORS)
        payload: dict[str, object] = {"status": status_payload, "meta": merged}
    else:
        payload = status_payload
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))
    logger.info("save_registry_state scope=%s path=%s count=%d", scope, path, len(status_payload))


def build_stock_meta(
    *,
    universe: str,
    symbol_count: int,
    mean_ic: dict[str, float],
    signs: dict[str, int] | None = None,
    fail_streak: dict[str, int] | None = None,
) -> dict[str, object]:
    meta: dict[str, object] = {
        "evaluated_at": datetime.now().isoformat(),
        "universe": universe,
        "symbol_count": symbol_count,
        "mean_ic": mean_ic,
        "min_live_factors": MIN_LIVE_FACTORS,
    }
    if signs is not None:
        meta["signs"] = signs
    if fail_streak is not None:
        meta["fail_streak"] = fail_streak
    return meta
